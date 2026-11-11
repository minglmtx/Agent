"""Hash verified proofs without binding temporary extraction locations.

Only byte-pinned file references within the supplied extraction directory are
relocated. Original control data, paths outside that directory and hashes are
unchanged. This does not verify or modify the proof itself.
"""
import hashlib
import json
from pathlib import Path
import re


def digest_native_gate(value, extraction_root):
    root = Path(extraction_root)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('Canonical absolute extraction root required')

    def normalize(item):
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if not isinstance(item, dict):
            return item
        result = {k: normalize(v) for k, v in item.items()}
        name = item.get('path')
        if isinstance(name, str) and Path(name).is_relative_to(root):
            if (set(item) != {'path', 'bytes', 'sha256'}
                    or type(item['bytes']) is not int or item['bytes'] < 0
                    or not isinstance(item['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', item['sha256'])
                    or '..' in Path(name).parts):
                raise ValueError('Temporary proof path is not an exact byte-pinned file')
            result['path'] = {'extraction_relative': str(Path(name).relative_to(root))}
        return result

    canonical = json.dumps(normalize(value), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()
