"""Scoped reset experiment: DB + cache, only for the three declared diagnostics.

Only explicitly declared file paths are restored. Search indexes and external
side effects still require separate admission checks.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import shutil,hashlib
from .admin_pilot import read_state,canonical_hash

TASK_IDS=('e5bd171b0b1550f4d11d','b27df1521a689351b66b','589ffd7db76177dbaeaa')

class AdminDatabaseSnapshot:
    def __init__(self,site,project,root,task_id, *, declared_scope=TASK_IDS):
        from .admin_pilot import SPECS
        if task_id not in declared_scope or not set(declared_scope).issubset(SPECS):
            raise ValueError('Task outside declared local reset validation scope')
        self.site=site;self.project=Path(project);self.root=Path(root);self.task_id=task_id
        self.state=Path(site.temp.name)/'webarena-admin'
        if not os.environ.get('SLURM_JOB_ID'):raise RuntimeError('Allocation required')
        # IsolatedAdminSite itself lives strictly inside the allocated node TMPDIR.
        self.state.resolve().relative_to(Path(os.environ['TMPDIR']).resolve())
        self.before=None
        self.export_scope=SPECS[task_id].get('mode')=='export'
        self.export_path=self.state/'app/var/export'
        self.export_backup=self.state/'diagnostic-export-baseline'
        self.export_existed=False
        self.export_hash=None
        self.artifacts=None
        paths=list(dict.fromkeys([*SPECS[task_id].get('filesystem_paths',[]),'var/training-mail','pub/media/training-assets']))
        if paths:
            from .admin_file_snapshot import AdminArtifactSnapshot
            if self.export_scope and 'var/export' in paths:raise ValueError('Export spool reset declared twice')
            self.artifacts=AdminArtifactSnapshot(self.state/'app',self.state/'diagnostic-artifact-baseline',paths)

    def command(self,*tail):
        return ['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/',
                '--bind',f'{self.state}:/state','--bind',f'{self.state}/app:/var/www/magento2',
                '--bind',f'{self.project}/cluster/admin-database-snapshot.php:/snapshot.php:ro',
                str(self.root/'containers/webarena/shopping-admin.sif'),*tail]

    def call(self,*tail):
        result=subprocess.run(self.command(*tail),capture_output=True,text=True,timeout=180)
        if result.returncode:raise RuntimeError('Isolated snapshot/cache command failed')
        return result.stdout

    def export_digest(self):
        if not self.export_path.exists():return None
        if self.export_path.is_symlink():raise RuntimeError('Export spool must not be a symlink')
        self.export_path.resolve().relative_to(self.state.resolve())
        rows=[]
        for path in sorted(self.export_path.rglob('*')):
            if path.is_symlink():raise RuntimeError('Export spool contains symlink')
            if path.is_file():rows.append((str(path.relative_to(self.export_path)),hashlib.sha256(path.read_bytes()).hexdigest()))
        return canonical_hash(rows)

    def save(self):
        start=time.monotonic();self.before=read_state(self.site,self.project,self.root)
        meta=json.loads(self.call('php','/snapshot.php','save'))
        if self.export_scope:
            self.export_hash=self.export_digest();self.export_existed=self.export_path.exists()
            if self.export_existed:shutil.copytree(self.export_path,self.export_backup)
            meta['export_spool_hash']=self.export_hash
        if self.artifacts:meta.update(self.artifacts.save())
        return {'seconds':time.monotonic()-start,'state_hash':canonical_hash(self.before),**meta}

    def restore(self):
        if self.before is None:raise RuntimeError('Snapshot must be saved first')
        # Resolve the target before any mutation; another foreground site's
        # environment must never select this instance's Redis database.
        redis_port=self.site.endpoints['WA_ADMIN_REDIS_PORT']
        start=time.monotonic();meta=json.loads(self.call('php','/snapshot.php','restore'))
        # Redis and application caches belong solely to this job's private site.
        self.call('redis-cli','-h','127.0.0.1','-p',redis_port,'FLUSHALL')
        self.call('php','/var/www/magento2/bin/magento','cache:flush')
        if self.export_scope:
            self.export_digest()  # Reject links/out-of-scope paths before removal.
            if self.export_path.exists():shutil.rmtree(self.export_path)
            if self.export_existed:shutil.copytree(self.export_backup,self.export_path)
            if self.export_digest()!=self.export_hash:raise RuntimeError('Export spool reset mismatch')
            meta['export_spool_restored']=True
        if self.artifacts:meta.update(self.artifacts.restore())
        after=read_state(self.site,self.project,self.root)
        equal=canonical_hash(after)==canonical_hash(self.before)
        if not equal:raise RuntimeError('Restored task state differs from cold-start baseline')
        return {'seconds':time.monotonic()-start,'state_hash':canonical_hash(after),'state_equal':equal,**meta}
