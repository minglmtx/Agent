"""Lossless, transactional JSON evidence with worker-local shared chunks.

Only explicit callers use this format. Ordinary JSON remains readable. Publish
the containing evidence tree, including .evidence.sqlite3, after closing writers.
One database avoids a file per chunk. No historical receipts are rewritten.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import zlib

VERSION = 'shared-json-evidence-v1'
STORE = '.evidence.sqlite3'


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def write(path, value, *, root, threshold=65536):
    from .io_utils import atomic_write_json
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root) or path == root or threshold < 1024:
        raise ValueError('Explicit containing evidence root and chunk threshold required')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = root / STORE
    if db.is_symlink():raise ValueError('Evidence database cannot be a symlink')
    with sqlite3.connect(db) as conn:
        db.chmod(0o600)
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE IF NOT EXISTS chunks (sha TEXT PRIMARY KEY, size INTEGER NOT NULL, payload BLOB NOT NULL)')
        cache = {}
        def pack(obj):
            raw = encoded(obj)
            if len(raw) < threshold:
                return ['literal', obj]
            # Stable logical identities avoid walking already seen subtrees.
            logical = hashlib.sha256(raw).hexdigest()
            if logical in cache:return cache[logical]
            if isinstance(obj, dict):node = ['dict', [[k, pack(v)] for k, v in obj.items()]]
            elif isinstance(obj, list):node = ['list', [pack(v) for v in obj]]
            else:node = ['literal', obj]
            data = encoded(node); digest = hashlib.sha256(data).hexdigest()
            existing = conn.execute('SELECT size,payload FROM chunks WHERE sha=?', (digest,)).fetchone()
            if existing:
                if existing[0] != len(data) or zlib.decompress(existing[1]) != data:
                    raise ValueError('Existing evidence chunk is corrupt')
            else:
                conn.execute('INSERT INTO chunks VALUES (?,?,?)', (digest, len(data), zlib.compress(data, 1)))
            ref = ['ref', digest, len(data)];cache[logical] = ref
            return ref
        node = pack(value)
    # Commit chunks before publishing the small document atomically. A crash
    # may leave unused chunks, but never a document referring to uncommitted data.
    document = {'storage_format': VERSION, 'store': os.path.relpath(db, path.parent),
                'logical_sha256': hashlib.sha256(encoded(value)).hexdigest(), 'node': node}
    atomic_write_json(path, document)
    path.chmod(0o600)
    return document


def resolve(path, document):
    if not isinstance(document, dict) or document.get('storage_format') != VERSION:
        return document
    path = Path(path).resolve();relative = Path(document['store'])
    if relative.is_absolute() or relative.name != STORE or any(p != '..' for p in relative.parts[:-1]):
        raise ValueError('Evidence store must be in this directory or an ancestor')
    db = path.parent / relative
    if db.is_symlink() or not db.is_file():raise ValueError('Evidence store missing or unsafe')
    active = set()
    with sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True) as conn:
        def unpack(node):
            if not isinstance(node, list) or not node:raise ValueError('Invalid evidence node')
            kind = node[0]
            if kind == 'literal' and len(node) == 2:return node[1]
            if kind == 'dict' and len(node) == 2:
                pairs=node[1]
                if len({p[0] for p in pairs})!=len(pairs):raise ValueError('Duplicate evidence key')
                return {k:unpack(v) for k,v in pairs}
            if kind == 'list' and len(node) == 2:return [unpack(v) for v in node[1]]
            if kind != 'ref' or len(node) != 3 or not re.fullmatch('[0-9a-f]{64}',node[1]):
                raise ValueError('Invalid evidence reference')
            digest=node[1]
            if digest in active:raise ValueError('Cyclic evidence reference')
            row=conn.execute('SELECT size,payload FROM chunks WHERE sha=?',(digest,)).fetchone()
            if row is None:raise ValueError('Evidence chunk missing')
            raw=zlib.decompress(row[1])
            if row[0] != node[2] or len(raw) != node[2] or hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('Evidence chunk hash/length mismatch')
            active.add(digest)
            try:return unpack(json.loads(raw))
            finally:active.remove(digest)
        value=unpack(document['node'])
    if hashlib.sha256(encoded(value)).hexdigest()!=document['logical_sha256']:
        raise ValueError('Restored logical evidence differs')
    return value


def read(path):
    return resolve(path, json.loads(Path(path).read_text()))
