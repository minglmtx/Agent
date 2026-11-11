"""Bind retained complete native GitLab gates to the ordinary actor runner.

Only pinned source records choose callbacks. Every selected raw member is
verified and restored locally; original two-cold validators run before hooks.
This adapter changes neither actor actions nor completion predicates.
"""
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace

from . import native_goal_dispatch as dispatch
from .frozen_native_family_adapter import FrozenNativeFamilyAdapter
from .native_proof_session import NativeProofSession
from .provider_review_catalog import identity
from .source_revision_binding import require_source_binding
from .gitlab_native_content import canonical_digest, VERSION as CONTENT_VERSION
from .gitlab_persisted_mutation import VERSION as MUTATION_VERSION


class _Adapter(FrozenNativeFamilyAdapter):
    def __init__(self, owner, kind):
        version = (owner.bridge_native.VERSION if kind == 'profile' else
                   dispatch.grouped.VERSION if kind == 'tag_commit' else
                   MUTATION_VERSION if kind == 'repository_file' else CONTENT_VERSION)
        super().__init__(family='reviewed-original-gitlab', driver_key='trusted-native-registry',
                         resolver=owner.resolve, public_goal=owner.public_goal,
                         feedback_versions=(version,), authorized_target_writes=kind in ('profile','repository_file'))
        self.owner, self.kind = owner, kind

    def enabled(self, c):
        return self.owner.kinds.get(c.get('source_task_id')) == self.kind

    def canonical(self, c):
        self.owner.bound(c)
        if not self.enabled(c):
            raise ValueError('Wrong original native protocol')
        return deepcopy({k:v for k,v in c.items() if k != 'admission_result'})

    def require_admission(self, c, descriptor):
        source = self.owner.resolve(self.owner.bound(c), descriptor)
        self.owner.verify(source, c, descriptor)
        return source['gate_return']

    def require_original_binding(self, c, original, inventory):
        self.owner.bound(c)
        return require_source_binding(self.canonical(c), original, inventory, domain='gitlab')

    def NativeReadHooks(self, c, descriptor, directory):
        sid = self.owner.bound(c)
        source = self.owner.resolve(sid, descriptor)
        self.owner.verify(source, c, descriptor)
        if self.kind == 'profile':
            hooks = self.owner.bridge_runtime.make_hooks(self.canonical(c), source['gate_return'], directory)
        else:
            private = source['cycles'][0]['controls']['initial_no_op']['private_reference']
            hooks = self.owner.existing.Hooks(self.canonical(c), private, directory, proof=source)
        # Hooks retain the precise private baseline needed for the live rollout.
        # Do not retain hundreds of MB of already-validated control snapshots.
        self.owner.release_proof()
        return hooks

    def public_goal(self, c):
        self.owner.bound(c)
        return self.owner.public_goal(c)

    def fields(self, c):
        self.owner.bound(c)
        return []


class ReviewedGitlabRegistry:
    def __init__(self, manifest, expected_sha256, *, project, selected_sources=None):
        self.project = Path(project).resolve()
        self.files = {}; self.loaded = {}; self.sources = {}; self.kinds = {}; self.items = {}
        self.registered = []; self.active = None; self.session = None; self.closed = False
        self.temp = tempfile.TemporaryDirectory(prefix='original-gitlab-proof-')
        self.root = Path(self.temp.name)
        try:
            config = json.loads(self.read(manifest, expected_sha256))
            if config.get('version') != 'reviewed-original-gitlab-registry-v1':
                raise ValueError('Explicit original native registry required')
            required = {'src/lab_generate_skill/reviewed_gitlab_registry.py',
                        'src/lab_generate_skill/native_goal_dispatch.py',
                        'src/lab_generate_skill/gitlab_public_bridge_runtime.py',
                        'src/lab_generate_skill/gitlab_public_bridge_native.py',
                        'scripts/native_documents/gitlab_bridge_cpu_controls.py',
                        'scripts/native_documents/gitlab_browser_lifecycle.py',
                        'scripts/native_documents/gitlab_existing_original_runtime.py',
                        'scripts/native_documents/public_task_input.py',
                        'scripts/run_site_navigation_once.py'}
            if not required <= config['runtime_files'].keys():
                raise ValueError('Original callbacks and ordinary runner must be pinned')
            for name,h in config['runtime_files'].items():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Relative runtime dependency required')
                self.read(self.project/name,h)
            for name in ('public_task_input','gitlab_browser_lifecycle','gitlab_existing_original_runtime','gitlab_bridge_cpu_controls'):
                if name in sys.modules:
                    raise ValueError('Conflicting original native module')
                path=self.project/'scripts/native_documents'/(name+'.py')
                spec=importlib.util.spec_from_file_location(name,path)
                module=importlib.util.module_from_spec(spec);sys.modules[name]=module;self.loaded[name]=module
                spec.loader.exec_module(module)
            self.public=self.loaded['public_task_input'];self.existing=self.loaded['gitlab_existing_original_runtime']
            self.bridge=self.loaded['gitlab_bridge_cpu_controls']
            from . import gitlab_public_bridge_runtime,gitlab_public_bridge_native
            self.bridge_runtime=gitlab_public_bridge_runtime;self.bridge_native=gitlab_public_bridge_native
            all_ids=[x['source_task_id'] for x in config['sources']]
            if not all_ids or len(set(all_ids))!=len(all_ids):
                raise ValueError('Distinct registered source identities required')
            selected=set(all_ids) if selected_sources is None else set(selected_sources)&set(all_ids)
            if not selected:
                raise ValueError('Nonempty selected native source set required')
            extract_jobs={}
            for item in config['sources']:
                sid=item['source_task_id']
                if sid not in selected:continue
                c=json.loads(self.read(**item['executed_contract']))['contract']
                if (c['source_task_id']!=sid or c['domain']!='gitlab' or c.get('heldout_quarantine') is not False
                        or item['split'] not in ('train','replacement_train')):
                    raise ValueError('Exact nonheldout GitLab source required')
                kind=item['kind']
                if kind not in ('profile','tag_commit','document','repository_file'):
                    raise ValueError('Unsupported original callback family')
                private=json.loads(self.read(**item['private_reference']))
                if kind=='document':
                    if (c.get('existing_shared_kind')!='document'
                            or canonical_digest(private)!=c['completion']['gitlab_native_content']['reference_sha256']):
                        raise ValueError('Exact complete native document reference required')
                    c=dict(c,native_content_reference_file=item['private_reference']['path'])
                elif kind=='tag_commit':
                    if c.get('existing_shared_kind')!='tag_commit':raise ValueError('Exact tag source required')
                elif kind=='repository_file':
                    if (c.get('existing_shared_kind')!='repository_file'
                            or c.get('family')!='gitlab_persisted_goal.repository_file'
                            or private.get('spec',{}).get('kind')!='repository_file'):
                        raise ValueError('Exact original native repository-file source required')
                else:
                    if c.get('gitlab_public_bridge',{}).get('kind')not in ('native_profile_ssh_key','native_profile_name'):
                        raise ValueError('Exact original native profile source required')
                    item=dict(item,case=json.loads(self.read(**item['original_case'])))
                    if self.bridge_runtime.contract_from_case(item['case'])!=c:
                        raise ValueError('Profile differs from its original complete public case')
                index=json.loads(self.read(**item['proof_index']))
                if index['source_task_id']!=sid:
                    raise ValueError('Proof index belongs to another source')
                for part in index['parts']:
                    arc=part['archive'];key=(arc['path'],arc['sha256'])
                    job=extract_jobs.setdefault(key,{'archive':arc,'members':{}})
                    for original,target in part['selected_members'].items():
                        dest=target['target'];path=Path(dest)
                        if path.is_absolute()or'..'in path.parts:
                            raise ValueError('Unsafe native member relocation')
                        previous=job['members'].get(original)
                        if previous is not None and previous!=target:
                            raise ValueError('Conflicting retained source member')
                        job['members'][original]=target
                self.sources[sid]=c;self.kinds[sid]=kind
                self.items[sid]=dict(item,private=private,index=index)
            # Shared original archives are streamed once per selected registry,
            # even when several source proofs refer to the same cold worker.
            for job in extract_jobs.values():self.extract(job)
            for sid,item in self.items.items():
                for alias in item['index'].get('aliases',[]):
                    source=self.root/alias['source'];target=self.root/alias['target']
                    if (Path(alias['source']).is_absolute() or '..' in Path(alias['source']).parts
                            or Path(alias['target']).is_absolute() or '..' in Path(alias['target']).parts
                            or not source.is_file() or source.is_symlink()
                            or hashlib.sha256(source.read_bytes()).hexdigest()!=alias['sha256']):
                        raise ValueError('Original private reference relocation differs')
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());self.files[target]=identity(target)
                dirs=[self.root/n for n in item['index']['directories']]
                if any(d.is_symlink()or not d.is_dir()for d in dirs)or len(dirs)!=2:
                    raise ValueError('Two actual restored cold source directories required')
                item['directories']=dirs
            for kind in sorted(set(self.kinds.values())):
                adapter=_Adapter(self,kind);name='original_gitlab_'+kind
                if kind=='tag_commit':dispatch.register_admission_bridge(name,adapter,base_protocol=dispatch.grouped)
                else:dispatch.register_protocol(name,adapter)
                self.registered.append((name,adapter))
            self.require_current()
        except BaseException:
            self.close();raise

    def read(self,path,sha256):
        p=Path(path)
        if not p.is_absolute()or p.is_symlink()or not p.is_file():raise ValueError('Regular absolute evidence required')
        before=identity(p);raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha256 or identity(p)!=before:raise ValueError('Native evidence changed: '+str(p))
        self.files[p]=before;return raw

    def extract(self,job):
        pin=job['archive'];p=Path(pin['path'])
        if not p.is_absolute()or p.is_symlink()or not p.is_file():raise ValueError('Regular retained archive required')
        before=identity(p);h=hashlib.sha256()
        with p.open('rb')as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        if h.hexdigest()!=pin['sha256']or identity(p)!=before:raise ValueError('Retained native archive changed')
        self.files[p]=before;seen=set();wanted=job['members']
        with tarfile.open(p,'r|gz')as t:
            for m in t:
                if m.name not in wanted:continue
                if not m.isfile()or m.name in seen:raise ValueError('Duplicate or nonregular native member')
                ref=wanted[m.name];dest=self.root/ref['target'];dest.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256();count=0
                with t.extractfile(m)as source,dest.open('xb')as out:
                    for b in iter(lambda:source.read(1024*1024),b''):h.update(b);count+=len(b);out.write(b)
                if count!=ref['bytes']or h.hexdigest()!=ref['sha256']:raise ValueError('Original member bytes differ')
                self.files[dest]=identity(dest);seen.add(m.name)
        if seen!=set(wanted):raise ValueError('Incomplete selected native source proof')

    def require_current(self):
        if self.closed or any(identity(p)!=state for p,state in self.files.items()):
            raise ValueError('Original native registry closed or evidence changed')

    def bound(self,c):
        self.require_current();sid=c.get('source_task_id')
        if {k:v for k,v in c.items()if k!='admission_result'}!=self.sources.get(sid):
            raise ValueError('Contract differs from exact current native materialization')
        return sid

    def resolve(self,sid,descriptor):
        self.require_current();item=self.items[sid]
        if descriptor!=item['descriptor']:raise ValueError('Original proof descriptor differs')
        if self.active is not None and self.active['contract']['source_task_id']==sid:return self.active
        self.release_proof();cycles=[json.loads((d/'cycle.json').read_text())for d in item['directories']]
        c=self.sources[sid];kind=self.kinds[sid]
        if kind=='profile':
            def gate(contract,values,dirs):
                if contract!=c:raise ValueError('Profile source contract differs')
                return self.bridge.require_two_cold(item['case'],values,dirs)
            from .source_revision_binding import fingerprint,binding
            result={'version':self.bridge_runtime.PROOF_VERSION,'contract_fingerprint':fingerprint(c),
                    'original_binding':binding(c),'actor_attempts':0,'api_calls':0,
                    'formal_preinference_lifecycle_verified':True,'cycles':cycles,'passed':True}
        else:
            def gate(contract,values,dirs):
                if self.existing.require_two_cold(contract,values,dirs)is not True:raise ValueError('Original native gate failed')
                for control in item['index'].get('extra_controls',[]):
                    folder=self.root/control['directory']
                    row=json.loads((folder/'native-private-receipt.json').read_text())
                    self.existing.require_control(contract,row,control['expected'],folder)
                return {'passed':True}
            result={'passed':True}
        reference=result['cycles'][0]['initial']if kind=='profile'else cycles[0]['controls']['initial_no_op']['private_reference']
        if reference!=item['private']:raise ValueError('Current private reference differs from both actual cold sources')
        self.active={'contract':deepcopy(c),'driver':SimpleNamespace(require_two_cold=gate),
                     'gate_return':result,'cycles':cycles,'directories':item['directories'],
                     'guard_files':[d.parent/'worker-cleanup.json' for d in item['directories']]}
        self.session=NativeProofSession()
        return self.active

    def verify(self,source,c,descriptor):
        self.require_current()
        canonical={k:v for k,v in c.items()if k!='admission_result'}
        def gate():
            if source['driver'].require_two_cold(canonical,source['cycles'],source['directories'])!=source['gate_return']:
                raise ValueError('Original full gate result changed')
        # resolve has already run the original gate. The session validates once
        # and detects changes before subsequent normal-entry calls.
        return self.session.verify(canonical,descriptor,source,gate)

    def release_proof(self):
        if self.session is not None:self.session.close()
        self.session=None;self.active=None

    def public_goal(self,c):
        self.bound(c)
        return self.bridge_runtime.public_goal(c)if self.kinds[c['source_task_id']]=='profile'else self.public.render(c)

    def partition(self,contracts):
        from .website_batch_profile import partition
        for c in contracts:self.bound(c)
        return [dict(rows=x['rows'],profile={**x['profile'],'original_gitlab_native':True},runner_arguments=[])
                for x in partition(contracts,'gitlab')]

    def runner(self,argv=None,**kwargs):
        import argparse
        self.require_current();p=argparse.ArgumentParser(add_help=False);p.add_argument('--manifest',type=Path,required=True)
        args,_=p.parse_known_args(argv);contracts=[json.loads(s)for s in args.manifest.read_text().splitlines()if s.strip()]
        if len(self.partition(contracts))!=1:raise ValueError('One compatible ordinary native profile required')
        runner=importlib.import_module('run_site_navigation_once')
        if Path(runner.__file__).resolve()!=self.project/'scripts/run_site_navigation_once.py':raise ValueError('Current ordinary runner required')
        return runner.main(argv,runtime_project=self.project,**kwargs)

    def close(self):
        self.release_proof()
        for name,module in reversed(self.registered):dispatch.unregister_protocol(name,module)
        self.registered=[]
        for name,module in reversed(list(self.loaded.items())):
            if sys.modules.get(name)is module:sys.modules.pop(name)
        self.loaded={}
        if self.temp is not None:self.temp.cleanup();self.temp=None
        self.closed=True

    def __enter__(self):self.require_current();return self
    def __exit__(self,*args):self.close()
