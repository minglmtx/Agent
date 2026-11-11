"""Read actual PBF header provenance without importing a website or database.

Bounding boxes prove an asset's declared extent only. They do not prove a road
exists, a geocoder identity matches, or a native route succeeds at runtime.
"""
import struct
import zlib
import json
import hashlib
from pathlib import Path


def _varint(body, index):
    value = shift = 0
    while index < len(body) and shift <= 63:
        byte = body[index]
        index += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, index
        shift += 7
    raise ValueError('Malformed bounded PBF protobuf varint')


def _fields(body):
    result = {}
    index = 0
    while index < len(body):
        tag, index = _varint(body, index)
        key, wire = tag >> 3, tag & 7
        if key == 0:
            raise ValueError('Invalid PBF protobuf field')
        if wire == 0:
            value, index = _varint(body, index)
        elif wire == 2:
            length, index = _varint(body, index)
            if index + length > len(body):
                raise ValueError('Truncated complete PBF field')
            value = body[index:index + length]
            index += length
        else:
            raise ValueError('Unsupported PBF header wire type')
        result.setdefault(key, []).append(value)
    return result


def pbf_header(path):
    path = Path(path)
    with path.open('rb') as stream:
        raw_size = stream.read(4)
        if len(raw_size) != 4:
            raise ValueError('PBF header length missing')
        size = struct.unpack('>I', raw_size)[0]
        if not 1 <= size <= 65536:
            raise ValueError('PBF BlobHeader exceeds bounded header budget')
        header = _fields(stream.read(size))
        if header.get(1) != [b'OSMHeader'] or len(header.get(3, [])) != 1 or not 1 <= header[3][0] <= 1024 * 1024:
            raise ValueError('Original complete PBF OSMHeader blob required')
        blob = _fields(stream.read(header[3][0]))
    if 1 in blob:
        raw = blob[1][0]
    elif 3 in blob and len(blob.get(2, [])) == 1 and blob[2][0] <= 1024 * 1024:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(blob[3][0], 1024 * 1024 + 1)
        if len(raw) != blob[2][0] or not decoder.eof or decoder.unused_data:
            raise ValueError('PBF header compression/length changed')
    else:
        raise ValueError('Unknown PBF header compression')
    values = _fields(raw)
    boxes = values.get(1)
    if not isinstance(boxes, list) or len(boxes) != 1:
        raise ValueError('Original PBF declared extent missing')
    fields = _fields(boxes[0])
    if set(fields) != {1, 2, 3, 4} or any(len(v) != 1 for v in fields.values()):
        raise ValueError('Exact PBF HeaderBBox fields required')
    decode = lambda number: ((number >> 1) ^ -(number & 1)) / 1e9
    box = {name: decode(fields[key][0]) for key, name in ((1, 'left'), (2, 'right'), (3, 'top'), (4, 'bottom'))}
    if not (-180 <= box['left'] < box['right'] <= 180 and -90 <= box['bottom'] < box['top'] <= 90):
        raise ValueError('PBF geographic extent invalid')
    return {'bytes': path.stat().st_size, 'bbox': box,
            'required_features': [b.decode() for b in values.get(4, [])],
            'generator': [b.decode() for b in values.get(16, [])],
            'replication_timestamp': values.get(32), 'native_route_coverage_proven': False}


_FULL_NATIVE_CACHE = {}

def _full_current_members(images, index, expected_pbf):
    """Hash all immutable native bytes once; reuse only unchanged exact inodes."""
    rows = [json.loads(line) for line in index.read_text().splitlines()]
    paths = {}
    signatures = []
    for row in rows:
        name = row['path']; relative = Path(name); path = images / relative
        if relative.is_absolute() or '..' in relative.parts or name in paths or path.is_symlink() or not path.is_file():
            raise ValueError('All unique regular native factory members required')
        stat = path.stat()
        if stat.st_size != row['bytes']:
            raise ValueError('Complete native factory member size changed')
        paths[name] = path
        signatures.append((name, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    actual = {path.relative_to(images).as_posix() for path in images.rglob('*') if path.is_file()}
    if actual != set(paths) | {'immutable-native-files.jsonl', 'native-assets.json'}:
        raise ValueError('Complete actual native factory member set differs')
    key = (str(images), hashlib.sha256(index.read_bytes()).hexdigest())
    if _FULL_NATIVE_CACHE.get(key) != signatures:
        for row in rows:
            h = hashlib.sha256()
            with paths[row['path']].open('rb') as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    h.update(chunk)
            if h.hexdigest() != row['sha256']:
                raise ValueError('Complete original native asset bytes changed: ' + row['path'])
        _FULL_NATIVE_CACHE[key] = signatures
    pbf_path = Path(expected_pbf['path'])
    matches = [row for row in rows if paths[row['path']] == pbf_path]
    if len(matches) != 1 or matches[0]['sha256'] != expected_pbf['sha256'] or matches[0]['bytes'] != expected_pbf['bytes']:
        raise ValueError('Complete actual PBF is not the same verified native factory member')
    return {'complete_current_native_member_bytes_verified': len(rows), 'cache_reuse_requires_exact_current_inode_size_mtime_ctime': True}

def native_asset_selection(manifest):
    """Select a complete real regional factory, not a static route response.

    This declaration is an environment revision. Producers must verify every
    immutable file before starting native services; it never admits a source.
    Nominatim, the actual API DB and each router must share the declared PBF.
    """
    path = Path(manifest)
    if path.is_symlink() or not path.is_absolute() or not path.is_file():
        raise ValueError('Versioned regular native regional manifest required')
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get('version') != 'map-native-region-assets-v1'
            or value.get('complete_native_assets_built') is not True
            or not isinstance(value.get('environment_revision'), str) or not value['environment_revision']
            or value.get('runtime_external_services_required') is not False
            or value.get('precomputed_task_routes_used') is not False
            or set(value.get('route_datasets', {})) != {'car', 'bike', 'foot'}):
        raise ValueError('Actual complete offline native assets, not fixtures, required')
    images = Path(value['images_directory'])
    if not images.is_absolute() or images.is_symlink() or not images.is_dir():
        raise ValueError('Real independent native image/data directory required')
    for mode, name in value['route_datasets'].items():
        if (not isinstance(name, str) or Path(name).name != name or not name.endswith('.osrm')
                or not (images / 'query-data/osrm' / mode / (name + '.properties')).is_file()):
            raise ValueError('Each transport mode requires a real native route dataset')
    pbf = value.get('pbf', {})
    actual = Path(pbf.get('path', ''))
    if (not actual.is_absolute() or actual.is_symlink() or not actual.is_file()
            or actual.stat().st_size != pbf.get('bytes') or len(str(pbf.get('sha256', ''))) != 64
            or pbf_header(actual) != pbf.get('header')):
        raise ValueError('Declared real PBF bytes/header unavailable')
    for role in ('nominatim', 'native_api_database', 'car', 'bike', 'foot'):
        if value.get('component_pbf_sha256', {}).get(role) != pbf['sha256']:
            raise ValueError('Native search/API/routing components do not share the exact regional PBF')
    index = images / 'immutable-native-files.jsonl'
    if not index.is_file() or hashlib.sha256(index.read_bytes()).hexdigest() != value.get('complete_files_manifest_sha256'):
        raise ValueError('Complete native asset file manifest missing or changed')
    value['full_current_member_verification'] = _full_current_members(images, index, pbf)
    value['selected_manifest_path'] = str(path)
    value['selected_manifest_sha256'] = hashlib.sha256(raw).hexdigest()
    return value
