"""One explicit runtime-repair attempt after interrupted terminal capture.

The old actor work stays intact. A valid scored actor failure cannot use this
path. Reuses the ordinary split, source/proof, exclusive lease and archive gates.
"""
import json
from pathlib import Path
from .unattempted_subset_continuation import UnattemptedSubsetContinuation
from .initialization_continuation import pinned, digest, regular_bytes

VERSION='closed-terminal-capture-repair-v1'
BINDING='terminal_capture_continuation'
LEASE='terminal-capture-repair-1'


def require_interrupted_capture(raw, contracts, requested, watchdog, job):
    task=watchdog.get('task_id')
    if (requested!=[task] or watchdog.get('evaluation')!={'status':'unknown','reward':None}
            or watchdog.get('watchdog',{}).get('enforcement')!='independent_process_group_termination'
            or watchdog.get('api_calls')!=0):
        raise ValueError('Only the exact unscored watchdog-interrupted task may be repaired')
    selected=[c for c in contracts if c['task_id']==task]
    if len(selected)!=1:raise ValueError('One unchanged original task required')
    prefix=task+'/'
    files={name[len(prefix):]:body for name,body in raw.items()if name.startswith(prefix)}
    if 'result.json' in files:
        raise ValueError('Existing result prohibits terminal-capture repair')
    read=lambda name:json.loads(files[name])
    claim=read('attempt-started.json');checkpoint=read('rollout-checkpoint.json')
    if claim!={'job':job,'task':task,'scripted':False}:
        raise ValueError('Original job and actor claim must match')
    if (checkpoint.get('interaction_complete')is not True
            or checkpoint.get('terminal_evaluation_complete')is not False
            or checkpoint.get('raw_file')!='rollout-raw.json' or checkpoint.get('api_calls')!=0):
        raise ValueError('Completed interaction and explicitly unfinished terminal evaluation required')
    rollout=read('rollout-raw.json');n=checkpoint.get('rounds')
    if (type(n)is not int or n<1 or rollout.get('task_id')!=task
            or rollout.get('rounds')!=n or rollout.get('finish_reason')!=checkpoint.get('finish_reason')):
        raise ValueError('Actual completed interaction disagrees with checkpoint')
    generations=[name for name in files if name.startswith('generation-')and name.endswith('.json')]
    if len(generations)!=n or any(read(name).get('status')!='complete' for name in generations):
        raise ValueError('Complete raw generation evidence required')
    # Even a separately saved finished score disqualifies this recovery route.
    for name in ('native-capture.json','native-terminal-capture.json','private-bridge-protection.json','private-persisted-protection.json'):
        if name in files and read(name).get('terminal_score_completed')is True:
            raise ValueError('Terminal score already completed')
    return selected


class TerminalCaptureContinuation(UnattemptedSubsetContinuation):
    version=VERSION
    binding_name=BINDING
    lease_name=LEASE

    def select_sources(self, raw, contracts, requested, watchdog):
        return require_interrupted_capture(raw,contracts,requested,watchdog,self.spec['old_job'])

    def retain_original_artifacts(self, raw, selected):
        self.old_claim_bytes={};self.allowed_old_artifacts={}
        for c in selected:
            task=c['task_id'];self.old_claim_bytes[task]=raw[task+'/attempt-started.json']
            folder=self.wave/'actor/0'/task
            for file in folder.iterdir():
                if not file.is_file() or file.is_symlink():raise ValueError('Unexpected retained actor artifact')
                if file.name=='attempt-archive.json':
                    marker=json.loads(regular_bytes(file))
                    if marker.get('archive_sha256')!=self.spec['raw']['archive_sha256'] or marker.get('automatic_retry')is not False:
                        raise ValueError('Original archive marker changed')
                elif raw.get(task+'/'+file.name)!=regular_bytes(file):
                    raise ValueError('Retained actor artifact differs from complete archive')
                self.allowed_old_artifacts[file.resolve()]=digest(file)
        if self.spec['retained_artifacts']!={str(k):v for k,v in self.allowed_old_artifacts.items()}:
            raise ValueError('Original retained artifact set changed')
        pin=self.spec['repair_review']
        review=json.loads(pinned(pin['path'],pin['sha256']))
        if (review.get('prior_job')!=self.old_job or review.get('old_missing_terminal_evidence_recovered')is not False
                or review.get('initial_and_terminal_evidence_preserved')is not True):
            raise ValueError('Explicit terminal-capture repair review required')

    def start(self,bundle,local_out,*,runtime_project,manifest_path):
        pins=self.spec.get('repair_runtime_pins',{})
        required={'scripts/run_archived_site_actor_bundle.py','scripts/run_site_navigation_once.py',
                  'src/lab_generate_skill/gitlab_persisted_goal_runtime.py',
                  'src/lab_generate_skill/site_batch_preparation.py'}
        if set(pins)!=required:raise ValueError('Reviewed setup, storage and terminal capture repairs required')
        for name,expected in pins.items():
            if digest(Path(runtime_project)/name)!=expected:
                raise ValueError('Frozen terminal repair differs from reviewed bytes')
        return super().start(bundle,local_out,runtime_project=runtime_project,manifest_path=manifest_path)
