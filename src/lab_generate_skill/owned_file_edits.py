"""Reversible edits to a private site's files, with ownership checks."""
from pathlib import Path
import hashlib
import os
import tempfile


class OwnedFileEdits:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.entries = {}
        self.closed = False

    def _path(self, path):
        path = Path(path).absolute()
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError('Site edit must be a regular private file')
        return path

    @staticmethod
    def _replace(path, body, mode):
        fd, temporary = tempfile.mkstemp(prefix='.owned-edit-', dir=path.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(body)
            temporary.chmod(mode)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def write_text(self, path, text):
        if self.closed:
            raise RuntimeError('Site edit owner is already closed')
        path = self._path(path)
        current = path.read_bytes() if path.exists() else None
        entry = self.entries.get(path)
        if entry is None:
            entry = {'before': current, 'mode': path.stat().st_mode & 0o777 if path.exists() else 0o644,
                     'after': current}
        if current != entry['after']:
            raise RuntimeError('Private site file changed outside its edit owner')
        body = text.encode('utf-8')
        self._replace(path, body, entry['mode'])
        entry['after'] = body
        self.entries[path] = entry

    def restore(self):
        if self.closed:
            return {'restored': True, 'files': len(self.entries)}
        # Check the whole set before overwriting any file owned by another edit.
        for path, entry in self.entries.items():
            self._path(path)
            if not path.is_file() or path.read_bytes() != entry['after']:
                raise RuntimeError('Cannot restore a site file modified by another owner')
        receipts = []
        for path, entry in reversed(list(self.entries.items())):
            if entry['before'] is None:
                path.unlink()
            else:
                self._replace(path, entry['before'], entry['mode'])
            receipts.append({'path': str(path.relative_to(self.root)),
                             'original_sha256': hashlib.sha256(entry['before']).hexdigest()
                             if entry['before'] is not None else None,
                             'restored': True})
        self.closed = True
        return {'restored': True, 'files': len(receipts), 'entries': receipts}
