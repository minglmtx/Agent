"""Bind the reviewed Tags source to its preserved ordinary artifact lifecycle."""
from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import sys
from .current_actor_entry import frozen_config, pinned_json, tags_registry_selection


class CurrentTagsRegistry:
    def __init__(self, reference, *, project, contracts):
        self.project=Path(project).resolve()
        config=frozen_config(self.project)
        if tags_registry_selection(contracts,config)!=reference:
            raise ValueError('Frozen Tags registry selection differs')
        self.config=pinned_json(reference['path'],reference['sha256'])
        self.contract=deepcopy(self.config['contract'])
        self.sources={self.contract['source_task_id']:self.contract}
        self.partition(contracts)
        reviewed=pinned_json(self.config['actual_review']['path'],self.config['actual_review']['sha256'])
        if (reviewed.get('passed')is not True or reviewed.get('source_task_id')!=self.contract['source_task_id']
                or reviewed.get('actual_generations',0)<1
                or reviewed.get('current_terminal_judgment',{}).get('status')not in('success','failure')):
            raise ValueError('Independently reviewed real Tags Actor required')
        code=self.project/'scripts/native_gitlab/tags'
        files=self.config['preserved_modules']
        required={'tags_runtime','tags_evidence_gate','tags_ordinary_hooks','tags_content_controls',
                  'run_tags_controls_helpers','tags_read_snapshot','private_tags_read_session','close_state'}
        if set(files)!=required:raise ValueError('Complete preserved Tags import closure required')
        for name,expected in files.items():
            path=code/(name+'.py')
            if path.is_symlink()or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('Preserved Tags implementation changed')
            loaded=sys.modules.get(name)
            if loaded is not None and Path(loaded.__file__).resolve()!=path:
                raise ValueError('Foreign Tags implementation already imported')
        sys.path.insert(0,str(code))
        try:
            self.module=importlib.import_module('tags_runtime')
            for name in required:
                module=importlib.import_module(name)
                if Path(module.__file__).resolve()!=code/(name+'.py'):
                    raise ValueError('Tags import escaped frozen code directory')
        finally:
            sys.path.remove(str(code))
        pin=self.config['source_registry']
        self.owner=self.module.Registry(pin['path'],pin['sha256'],project=self.project)
        if self.owner.contract!=self.contract:raise ValueError('Preserved source definition changed')
        self.owner.gate.update(first_actor_still_required=False,actual_actor_review=self.config['actual_review'])
        self.live=False

    def partition(self,contracts):
        if len(contracts)!=1 or {k:v for k,v in contracts[0].items()if k!='admission_result'}!=self.contract:
            raise ValueError('One exact Tags source contract required')
        return [dict(rows=contracts,profile={'tags_subscription':'native-tags-v1'},runner_arguments=[])]

    def __enter__(self):
        if self.live:raise ValueError('Tags registry already active')
        self.owner.__enter__();self.live=True;return self

    def runner(self,argv=None,**kwargs):
        import argparse,json
        if not self.live:raise ValueError('Live Tags proof owner required')
        parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--manifest',type=Path,required=True)
        args,_=parser.parse_known_args(argv)
        self.partition([json.loads(l)for l in args.manifest.read_text().splitlines()if l.strip()])
        return self.owner.runner(argv,**kwargs)

    def __exit__(self,*args):
        try:return self.owner.__exit__(*args)
        finally:self.live=False
