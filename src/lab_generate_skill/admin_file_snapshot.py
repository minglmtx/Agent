"""Restore declared private Magento artifact directories alongside database state."""
import hashlib,json,shutil,stat
from pathlib import Path

ALLOWED_PATHS=frozenset({'pub/media/catalog/product','pub/media/tmp/catalog/product',
                        'pub/media/wysiwyg','pub/media/.thumbs','var/export','var/training-mail','pub/media/training-assets'})


def tree_digest(directory):
    directory=Path(directory)
    if directory.is_symlink():raise RuntimeError('Artifact directory cannot be a symlink')
    if not directory.exists():return None
    if not directory.is_dir():raise RuntimeError('Expected artifact directory')
    rows=[]
    for p in [directory,*sorted(directory.rglob('*'))]:
        if p.is_symlink():raise RuntimeError('Artifact tree contains a symlink')
        mode=stat.S_IMODE(p.stat().st_mode);name=str(p.relative_to(directory))
        if p.is_dir():rows.append((name,'directory',mode))
        elif p.is_file():
            h=hashlib.sha256()
            with p.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            rows.append((name,'file',mode,p.stat().st_size,h.hexdigest()))
        else:raise RuntimeError('Artifact tree contains a non-regular entry')
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


class AdminArtifactSnapshot:
    def __init__(self,app_root,backup,paths):
        self.app=Path(app_root).resolve();self.backup=Path(backup);self.paths=tuple(paths);self.baseline=None
        if not self.paths or len(set(self.paths))!=len(self.paths) or not set(self.paths)<=ALLOWED_PATHS:
            raise ValueError('Artifact reset must declare distinct supported application paths')
        self.backup.resolve().relative_to(self.app.parent)
        if self.backup.resolve()==self.app or self.app in self.backup.resolve().parents:
            raise ValueError('Artifact backup must be outside the application tree')
        for relative in self.paths:self.checked_path(relative)

    def checked_path(self,relative):
        path=self.app/relative
        for part in [path,*path.parents]:
            if part==self.app:break
            if part.is_symlink():raise RuntimeError('Artifact path contains a symlink')
        path.resolve().relative_to(self.app)
        return path

    def save(self):
        self.backup.mkdir(exist_ok=False)
        baseline={}
        for index,relative in enumerate(self.paths):
            path=self.checked_path(relative);expected=tree_digest(path);baseline[relative]=expected
            if expected is not None:
                dest=self.backup/str(index);shutil.copytree(path,dest)
                if tree_digest(dest)!=expected or tree_digest(path)!=expected:raise RuntimeError('Artifact changed while snapshotting')
        self.baseline=baseline
        (self.backup/'manifest.json').write_text(json.dumps(baseline,indent=2))
        return {'artifact_paths':list(self.paths),'artifact_hashes':baseline}

    def restore(self):
        if self.baseline is None:raise RuntimeError('Artifact snapshot not saved')
        # Validate every target and every backup before modifying any target.
        for index,relative in enumerate(self.paths):
            tree_digest(self.checked_path(relative))
            if tree_digest(self.backup/str(index))!=self.baseline[relative]:raise RuntimeError('Artifact baseline changed')
        for index,relative in enumerate(self.paths):
            path=self.checked_path(relative)
            if path.exists():shutil.rmtree(path)
            if self.baseline[relative] is not None:
                path.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(self.backup/str(index),path)
            if tree_digest(path)!=self.baseline[relative]:raise RuntimeError('Artifact reset mismatch')
        return {'artifacts_restored':True,'artifact_hashes':dict(self.baseline)}
