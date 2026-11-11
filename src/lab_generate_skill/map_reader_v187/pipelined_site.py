"""Overlap only the unchanged full app snapshot clone with other Map startup.

The original clone command and four copy workers are retained. No PostgreSQL
process may use the app directory until the clone completes. All processes stay
owned by the ordinary factory; the native reset guard and baseline stay intact.
"""
from pathlib import Path
import json,os,subprocess,sys,time
from lab_generate_skill.map_existing_account_site import IsolatedMapExistingAccountSite

class PipelinedMapExistingAccountSite(IsolatedMapExistingAccountSite):
    def start_search(self,port):
        if not self.with_geographic_baseline or os.environ.get('LAB_MAP_PARALLEL_APP_CLONE','1')!='1':raise ValueError('Reviewed full geographic four-worker clone required')
        state=self.state/'frontend';destination=state/'pg'
        if destination.exists():raise ValueError('Snapshot destination must be fresh')
        import lab_generate_skill
        script=Path(lab_generate_skill.__file__).resolve().parents[2]/'scripts/clone_map_snapshot.py'
        self._app_clone_started=time.monotonic();self._app_clone_destination=destination
        self._app_clone=self.launch([sys.executable,str(script),'--source',str(self.images/'app-baseline/postgres'),'--destination',str(destination),'--progress',str(self.logs/'app-clone-progress.json')],'clone_app_geographic_database')
        return super().start_search(port)

    def prepare_app_database(self,state,db):
        if state/'pg'!=self._app_clone_destination:raise ValueError('App clone must bind the original frontend directory')
        process=self._app_clone;remaining=1800-(time.monotonic()-self._app_clone_started)
        try:
            if process.poll()is None and remaining<=0:raise TimeoutError('Full app snapshot clone exceeded its original1800second limit')
            rc=process.wait(timeout=max(.001,remaining))
        except (subprocess.TimeoutExpired,TimeoutError):
            self.stop_service('clone_app_geographic_database',graceful_timeout=1);raise TimeoutError('Full app snapshot clone exceeded its original1800second limit')
        if rc:raise RuntimeError('Full app snapshot clone failed; inspect owned clone log')
        receipt=json.loads((self.logs/'app-clone-progress.json').read_text())
        if receipt.get('status')!='complete' or receipt.get('source_modified')is not False or receipt['seconds']>1800:raise ValueError('Completed unchanged-source clone receipt required')
        self.event('clone_app_geographic_database_overlap',self._app_clone_started,returncode=rc,snapshot_copy_seconds=receipt['seconds'],same_original_clone_command=True,postgres_start_waited_for_complete_copy=True)
        (state/'pg').chmod(0o700)
