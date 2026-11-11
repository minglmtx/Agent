"""Native hierarchy, Metrics, CSV and template evidence in one ordinary registry.

Large first-control records remain in their original archives. A descriptor
is never sufficient admission: each actual gate is replayed and guarded once.
"""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile

from . import gitlab_remaining_runtime as native
from . import gitlab_template_runtime as template
from . import gitlab_remaining_components as component
from . import native_goal_dispatch as dispatch
from .frozen_native_family_adapter import FrozenNativeFamilyAdapter
from .native_proof_session import NativeProofSession
from .reviewed_gitlab_registry import ReviewedGitlabRegistry


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class _Adapter(FrozenNativeFamilyAdapter):
    def __init__(self,owner,family):
        self.owner=owner
        super().__init__(family=family,driver_key='gitlab-remaining',resolver=owner.resolve,
            public_goal=component.public_goal,
            feedback_versions=((component.grouped.VERSION,) if family=='native_monitoring_section' else (component.VERSION,)),
            hook_protocol='private_reference_class',proof_session=owner.proof_session,
            owns_csv_transport=family=='native_all_merge_request_csv',
            authorized_target_writes=family=='native_repository_template')

    def enabled(self,c):
        return c.get('source_task_id')in self.owner.sources and super().enabled(c)

    def canonical(self,c):
        self.owner.bound(c)
        return super().canonical(c)

    def NativeReadHooks(self,c,descriptor,directory):
        source=self._verified_source(c,descriptor)
        first=(source['gate_return']['first_control']if 'groups'in source
               else source['cycles'][0]['controls']['initial_no_op'])
        return source['driver'].Hooks(self.canonical(c),first['private_reference'],directory,
            proof=source,proof_session=self.proof_session)


class ReviewedRemainingRegistry:
    read=ReviewedGitlabRegistry.read
    extract=ReviewedGitlabRegistry.extract
    require_current=ReviewedGitlabRegistry.require_current
    bound=ReviewedGitlabRegistry.bound

    def __init__(self,manifest,expected_sha256,*,project,selected_sources=None):
        self.project=Path(project).resolve();self.files={};self.sources={};self.items={}
        self.closed=False;self.active=None;self.adapters=[];self.proof_session=NativeProofSession()
        self.temp=tempfile.TemporaryDirectory(prefix='current-native-remaining-')
        self.root=Path(self.temp.name);self.manifest=Path(manifest)
        try:
            cfg=json.loads(self.read(manifest,expected_sha256))
            if cfg.get('version')!='reviewed-native-remaining-registry-v1':
                raise ValueError('Explicit current native registry required')
            required={'src/lab_generate_skill/'+n for n in (
                'reviewed_remaining_registry.py','gitlab_remaining_runtime.py','gitlab_template_runtime.py',
                'gitlab_remaining_components.py','gitlab_remaining_native.py','gitlab_remaining_state.py',
                'gitlab_remaining_public.py','gitlab_template_native.py','gitlab_template_state.py',
                'native_template_reference.rb','native_template_worker.rb','native_csv_supplement_admission.py',
                'native_template_supplement_admission.py','native_proof_session.py','frozen_native_family_adapter.py',
                'current_actor_entry.py','current_actor_submission.py','native_goal_dispatch.py')}
            required.add('scripts/run_site_navigation_once.py')
            if not required<=cfg['runtime_files'].keys():raise ValueError('Native dependencies missing')
            for name,h in cfg['runtime_files'].items():
                if Path(name).is_absolute()or '..'in Path(name).parts:raise ValueError('Relative code pin required')
                self.read(self.project/name,h)
            ids=[r['source_task_id']for r in cfg['sources']]
            if not ids or len(set(ids))!=len(ids):raise ValueError('Distinct sources required')
            selected=set(ids)if selected_sources is None else set(ids)&set(selected_sources)
            if not selected:raise ValueError('Nonempty native selection required')
            jobs={}
            for item in cfg['sources']:
                sid=item['source_task_id']
                if sid not in selected:continue
                record=json.loads(self.read(**item['executed_contract']));c=record['contract'];gate=record['gate']
                if(c.get('source_task_id')!=sid or c.get('domain')!='gitlab'
                   or c.get('heldout_quarantine')is not False or item['split']not in('train','replacement_train')):
                    raise ValueError('Exact training source contract required')
                component.enabled(c)
                if gate.get('passed')is not True or gate.get('contract')!=c or gate.get('source_task_id')!=sid:
                    raise ValueError('Original complete gate required')
                index=json.loads(self.read(**item['proof_index']))
                if index['source_task_id']!=sid:raise ValueError('Source-bound proof index required')
                for part in index['parts']:
                    arc=part['archive'];job=jobs.setdefault((arc['path'],arc['sha256']),{'archive':arc,'members':{}})
                    for name,target in part['selected_members'].items():
                        dest=Path(target['target'])
                        if dest.is_absolute()or '..'in dest.parts:raise ValueError('Safe proof destination required')
                        if name in job['members']and job['members'][name]!=target:raise ValueError('Conflicting shared proof')
                        job['members'][name]=target
                descriptor={'version':'current-native-remaining-source-v1','source_task_id':sid,
                    'contract_sha256':digest(c),'gate_sha256':record['full_gate_sha256'],
                    'proof_index_sha256':item['proof_index']['sha256']}
                if descriptor!=item['descriptor']:raise ValueError('Exact native descriptor required')
                self.sources[sid]=c;self.items[sid]=dict(item,index=index,gate=gate,full_gate_sha256=record['full_gate_sha256'])
            for job in jobs.values():self.extract(job)
            for family in sorted({c['family']for c in self.sources.values()}):
                adapter=_Adapter(self,family);name='current_remaining:'+family
                if family=='native_monitoring_section':
                    dispatch.register_admission_bridge(name,adapter,base_protocol=dispatch.grouped,feedback_owner=self)
                else:dispatch.register_protocol(name,adapter,feedback_owner=self)
                self.adapters.append((name,adapter))
            self.require_current()
        except BaseException:
            self.close();raise

    def path(self,name):
        relative=Path(name)
        if relative.is_absolute()or '..'in relative.parts:raise ValueError('Relative proof member required')
        p=self.root/relative
        if p.is_symlink()or not p.exists():raise ValueError('Original proof member missing')
        return p

    def resolve(self,sid,descriptor):
        self.require_current();item=self.items[sid]
        if descriptor!=item['descriptor']:raise ValueError('Native source descriptor differs')
        if self.active is not None and self.active['contract']['source_task_id']==sid:return self.active
        self.active=None;idx=item['index'];gate=deepcopy(item['gate']);c=self.sources[sid]
        source=dict(contract=deepcopy(c),driver=template if c['family']=='native_repository_template'else native)
        if idx.get('groups'):
            groups=[]
            for g in idx['groups']:
                groups.append({k:str(self.path(v))if k.endswith('_directory')else v for k,v in g.items()})
            gate['first_control']=json.loads(self.path(idx['first_control']).read_text())
            source.update(version=gate['version'],groups=groups,directories=[self.path(n)for n in idx['directories']])
        else:
            dirs=[self.path(n)for n in idx['directories']]
            if len(dirs)!=2:raise ValueError('Two independent full cycles required')
            source.update(cycles=[json.loads((d/'cycle.json').read_text())for d in dirs],directories=dirs,
                guard_files=[d.parent/'worker-cleanup.json'for d in dirs])
        if digest(gate)!=item['full_gate_sha256']:raise ValueError('Original full gate differs from its digest')
        source['gate_return']=gate;self.active=source
        return source

    def partition(self,contracts):
        from .website_batch_profile import partition
        for c in contracts:self.bound(c)
        return [dict(rows=g['rows'],profile={**g['profile'],'current_native_remaining':True},runner_arguments=[])
                for g in partition(contracts,'gitlab')]

    def runner(self,argv=None,**kwargs):
        import argparse
        self.require_current();parser=argparse.ArgumentParser(add_help=False)
        parser.add_argument('--manifest',type=Path,required=True);args,_=parser.parse_known_args(argv)
        contracts=[json.loads(s)for s in args.manifest.read_text().splitlines()if s.strip()]
        if len(self.partition(contracts))!=1:raise ValueError('One compatible native profile required')
        runner=importlib.import_module('run_site_navigation_once')
        if Path(runner.__file__).resolve()!=self.project/'scripts/run_site_navigation_once.py':raise ValueError('Current ordinary runner required')
        return runner.main(argv,runtime_project=self.project,**kwargs)

    def close(self):
        for name,adapter in self.adapters:dispatch.unregister_protocol(name,adapter)
        self.adapters=[];self.active=None;self.proof_session.close()
        if self.temp is not None:self.temp.cleanup();self.temp=None
        self.closed=True

    def __enter__(self):self.require_current();return self
    def __exit__(self,*args):self.close()
