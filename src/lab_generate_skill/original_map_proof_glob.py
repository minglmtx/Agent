"""Enumerate pinned archived source files at their original producer paths.

The old transport supported reading a known filename, but Path.glob silently
looked at a deleted node-local directory. Only manifested files are enumerated;
normal predicates and original body hashes remain unchanged.
"""
from contextlib import contextmanager
from fnmatch import fnmatchcase
from pathlib import Path


def matches(parts, pattern):
    if not pattern:return not parts
    if pattern[0]=='**':
        return matches(parts,pattern[1:]) or bool(parts and matches(parts[1:],pattern))
    return bool(parts and fnmatchcase(parts[0],pattern[0]) and matches(parts[1:],pattern[1:]))


def supplier_with_glob(original):
    @contextmanager
    def supplied(restored):
        files={};directories=set()
        for item in restored:
            for name,target in item['aliases'].items():
                name=Path(name);relative=target.relative_to(item['restore_root'])
                row=item['files'][relative.as_posix()]
                if name in files and files[name]!=row:raise ValueError('Conflicting archived file listing')
                files[name]=row
                directories.update(list(name.parents)[:len(relative.parts)])
        with original(restored):
            old=Path.glob
            def glob(path,pattern,*args,**kwargs):
                if path not in directories:
                    yield from old(path,pattern,*args,**kwargs);return
                pattern=Path(pattern)
                if args or kwargs or pattern.is_absolute() or '..' in pattern.parts:
                    raise ValueError('Bound relative archive file glob required')
                for name in sorted(files):
                    try:relative=name.relative_to(path)
                    except ValueError:continue
                    if matches(relative.parts,pattern.parts):
                        # Existing source transport verifies the full archived
                        # bytes before supplying a file to the unchanged gate.
                        with name.open('rb') as handle:handle.read()
                        yield name
            Path.glob=glob
            try:yield files
            finally:Path.glob=old
    return supplied
