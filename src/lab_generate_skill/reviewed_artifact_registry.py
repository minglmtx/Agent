"""Current artifact protocols backed by exact retained native controls.

No archived runtime or task-supplied imports are installed. Shared archives are
read once, and only the active source's large control vectors remain in memory.
"""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile

from . import native_artifact_runtime as native
from . import native_goal_dispatch as dispatch
from .frozen_native_artifact_adapter import FrozenNativeArtifactAdapter
from .native_artifact_interface import _session_extension, actor_bridge
from .native_proof_session import NativeProofSession
from .reviewed_gitlab_registry import ReviewedGitlabRegistry


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class _Adapter(FrozenNativeArtifactAdapter):
    def __init__(self, owner):
        self.owner = owner
        super().__init__(family=tuple(sorted(native.FAMILIES)), driver_key='gitlab-artifact-source',
            resolver=owner.resolve, public_goal=native.public_goal,
            feedback_versions=(native.VERSION,), bind_client_session=owner.bind_client,
            proof_session=owner.proof_session)

    def enabled(self, c):
        return c.get('source_task_id') in self.owner.sources and super().enabled(c)

    def canonical(self, c):
        self.owner.bound(c)
        return super().canonical(c)

    def NativeReadHooks(self, contract, descriptor, directory):
        source=self._verified_source(contract,descriptor)
        current=self.canonical(contract)
        private=source['cycles'][0]['controls']['initial_no_op']['private_reference']
        hooks=native.Hooks(current,private,directory,proof=source,proof_session=self.proof_session)
        self._pending[id(hooks)]=(hooks,source,current,Path(directory).resolve(),descriptor)
        return hooks


class ReviewedArtifactRegistry:
    # These helpers verify bytes and paths only; they do not import legacy
    # callbacks or construct the unrelated original GitLab registry.
    read = ReviewedGitlabRegistry.read
    extract = ReviewedGitlabRegistry.extract
    require_current = ReviewedGitlabRegistry.require_current
    bound = ReviewedGitlabRegistry.bound

    def __init__(self, manifest, expected_sha256, *, project, selected_sources=None):
        self.project=Path(project).resolve();self.files={};self.sources={};self.items={}
        self.closed=False;self.active=None;self.registered=False;self.adapter=None
        self.proof_session=NativeProofSession()
        self.temp=tempfile.TemporaryDirectory(prefix='current-artifact-proof-')
        self.root=Path(self.temp.name);self.manifest=Path(manifest)
        try:
            config=json.loads(self.read(manifest, expected_sha256))
            if config.get('version')!='reviewed-native-artifact-registry-v1':
                raise ValueError('Explicit current artifact registry required')
            required={'src/lab_generate_skill/'+name+'.py' for name in (
                'reviewed_artifact_registry','native_artifact_runtime','native_artifact_state',
                'native_artifact_client','native_artifact_workspace','native_artifact_page_lifetime',
                'native_artifact_interface','frozen_native_artifact_adapter','frozen_native_family_adapter',
                'native_proof_session','native_goal_dispatch','constrained_actions')}
            required.add('scripts/run_site_navigation_once.py')
            required.update({'scripts/gitlab_calendar_account_fixture.py',
                             'scripts/gitlab_calendar_account_fixture.rb'})
            if not required <= config['runtime_files'].keys():
                raise ValueError('Full artifact runner, gate and public interface pins required')
            for name,h in config['runtime_files'].items():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Relative runtime dependency required')
                self.read(self.project/name,h)
            all_ids=[r['source_task_id'] for r in config['sources']]
            if not all_ids or len(set(all_ids))!=len(all_ids):
                raise ValueError('Distinct artifact sources required')
            selected=set(all_ids) if selected_sources is None else set(all_ids)&set(selected_sources)
            if not selected: raise ValueError('Nonempty selected artifact source set required')
            jobs={}
            for item in config['sources']:
                sid=item['source_task_id']
                if sid not in selected: continue
                record=json.loads(self.read(**item['executed_contract']))
                c=record['contract'];gate=record['gate']
                if (c.get('source_task_id')!=sid or c.get('domain')!='gitlab'
                        or c.get('heldout_quarantine') is not False
                        or item['split'] not in ('train','replacement_train')):
                    raise ValueError('Exact nonheldout artifact contract required')
                native.enabled(c)
                if gate.get('passed') is not True or gate.get('contract')!=c or gate.get('fresh_cycles')!=2:
                    raise ValueError('Complete reviewed native source gate required')
                index=json.loads(self.read(**item['proof_index']))
                if index['source_task_id']!=sid or len(index['directories'])!=2:
                    raise ValueError('Two complete source-bound cold directories required')
                for part in index['parts']:
                    arc=part['archive'];key=(arc['path'],arc['sha256'])
                    job=jobs.setdefault(key,{'archive':arc,'members':{}})
                    for member,target in part['selected_members'].items():
                        dest=Path(target['target'])
                        if dest.is_absolute() or '..' in dest.parts:
                            raise ValueError('Unsafe native proof relocation')
                        if member in job['members'] and job['members'][member]!=target:
                            raise ValueError('Conflicting shared artifact evidence')
                        job['members'][member]=target
                descriptor={'version':'current-native-artifact-source-v1','source_task_id':sid,
                    'contract_sha256':digest(c),'gate_sha256':digest(gate),
                    'proof_index_sha256':item['proof_index']['sha256']}
                if item['descriptor']!=descriptor: raise ValueError('Exact artifact descriptor binding required')
                self.sources[sid]=c;self.items[sid]=dict(item,index=index,gate=gate)
            for job in jobs.values(): self.extract(job)
            for item in self.items.values():
                if any(Path(n).is_absolute() or '..' in Path(n).parts for n in item['index']['directories']):
                    raise ValueError('Unsafe native cold directory relocation')
                dirs=[self.root/n for n in item['index']['directories']]
                if any(d.is_symlink() or not d.is_dir() for d in dirs):
                    raise ValueError('Original native cold directory missing')
                item['directories']=dirs
            self.adapter=_Adapter(self)
            dispatch.register_protocol('current_native_artifacts',self.adapter);self.registered=True
            self.require_current()
        except BaseException:
            self.close();raise

    def resolve(self,sid,descriptor):
        self.require_current();item=self.items[sid]
        if descriptor!=item['descriptor']: raise ValueError('Source artifact descriptor differs')
        if self.active is not None and self.active['contract']['source_task_id']==sid:
            return self.active
        self.active=None
        cycles=[json.loads((d/'cycle.json').read_text()) for d in item['directories']]
        self.active={'contract':deepcopy(self.sources[sid]),'driver':native,
            'gate_return':item['gate'],'cycles':cycles,'directories':item['directories'],
            'guard_files':[d.parent/'worker-cleanup.json' for d in item['directories']],
            'native_packet':{'candidate_root':str(self.project),'plan_path':str(self.manifest)}}
        return self.active

    def bind_client(self,base_factory,*,artifact_root,site_origin,candidate_root,plan,
                    driver_module,case,cycles,directories,hooks,current_account_auth):
        sid=self.bound(case);source=self.resolve(sid,self.items[sid]['descriptor'])
        # The adapter verifies the complete native gate and change guard again
        # immediately before calling this binder; these are the same objects.
        if (driver_module is not native or cycles is not source['cycles']
                or directories!=source['directories'] or hooks.contract!=case
                or not hooks.prepared or hooks.site.url!=site_origin
                or Path(candidate_root).resolve()!=self.project
                or Path(artifact_root).resolve()!=hooks.directory.resolve()/'client-live'):
            raise ValueError('Client binding differs from the admitted native attempt')
        return _session_extension(base_factory,artifact_root=artifact_root,site_origin=site_origin,
            source_task_id=sid,hooks=hooks,current_account_auth=current_account_auth)

    def partition(self,contracts):
        from .website_batch_profile import partition
        for c in contracts: self.bound(c)
        return [dict(rows=g['rows'],profile={**g['profile'],'current_native_artifacts':True},
                     runner_arguments=[]) for g in partition(contracts,'gitlab')]

    def runner(self,argv=None,**kwargs):
        import argparse
        self.require_current();parser=argparse.ArgumentParser(add_help=False)
        parser.add_argument('--manifest',type=Path,required=True);args,_=parser.parse_known_args(argv)
        contracts=[json.loads(s) for s in args.manifest.read_text().splitlines() if s.strip()]
        if len(self.partition(contracts))!=1: raise ValueError('One compatible artifact profile required')
        runner=importlib.import_module('run_site_navigation_once')
        if Path(runner.__file__).resolve()!=self.project/'scripts/run_site_navigation_once.py':
            raise ValueError('Current ordinary runner required')
        with actor_bridge(runner,self.adapter):
            return runner.main(argv,runtime_project=self.project,**kwargs)

    def close(self):
        if self.registered: dispatch.unregister_protocol('current_native_artifacts',self.adapter)
        self.registered=False;self.active=None;self.proof_session.close()
        if self.temp is not None: self.temp.cleanup();self.temp=None
        self.closed=True

    def __enter__(self): self.require_current();return self
    def __exit__(self,*args): self.close()
