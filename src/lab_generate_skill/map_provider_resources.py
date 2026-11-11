"""Join byte-pinned provider archives without copying them onto shared storage.

These are environment resources, not task admission or success evidence.
Materialize once in a worker's private local directory; never fetch at runtime.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

from PIL import Image

from .map_provider_coverage import URLS, provider_plans
from .map_route_normal_capture import fingerprint


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_archive(source):
    data = Path(source['archive']).read_bytes()
    if sha(data) != source['sha256']:
        raise ValueError('Provider archive changed')
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if (not item.isfile() or path.is_absolute() or '..' in path.parts
                    or str(path) != item.name or item.name in result):
                raise ValueError('Noncanonical or duplicate provider archive member')
            result[item.name] = archive.extractfile(item).read()
    return result


def member(files, record):
    data = files[record['member']]
    if len(data) != record['bytes'] or sha(data) != record['sha256']:
        raise ValueError('Provider member changed')
    return data


def validate_tile(provider, key, record, files):
    parts = key.removesuffix('.png').split('/')
    if len(parts) != 3 or any(not p.isdigit() for p in parts):
        raise ValueError('Explicit tile coordinate required')
    z, x, y = map(int, parts)
    if key != f'{z}/{x}/{y}.png' or not 0 <= z <= 20 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError('Tile coordinate outside declared map')
    if record['member'] != f'assets/providers/{provider}/tiles/{key}':
        raise ValueError('Tile path/provider mismatch')
    normalized = member(files, record)
    original = member(files, record['original_member'])
    receipt = json.loads(member(files, record['http_receipt']))
    expected_url = URLS[provider].format(z=z, x=x, y=y)
    if (receipt.get('http_status') != 200 or receipt.get('url') != expected_url
            or receipt.get('final_url') != expected_url
            or receipt.get('sha256') != sha(original)
            or receipt.get('bytes') != len(original)):
        raise ValueError('Original HTTP response does not bind this provider tile')
    for data in (original, normalized):
        with Image.open(io.BytesIO(data)) as image:
            if image.size != (256, 256) or sha(image.convert('RGBA').tobytes()) != record['decoded_rgba_sha256']:
                raise ValueError('Original and normalized tile pixels differ')
    if receipt.get('decoded_rgba_sha256') != record['decoded_rgba_sha256']:
        raise ValueError('HTTP receipt pixel identity differs')


def build_resources(candidates, sources, *, native_initial_views=None, tile_sources=None):
    """Cover exactly the original task views, deduplicating shared tiles."""
    plans = provider_plans(candidates,native_initial_views=native_initial_views)
    selections = dict(tile_sources or {})
    consumed = set()
    contracts = {c['source_task_id']: c['candidate_completion'] for c in candidates}
    archives = {}
    manifests = {}
    for source in sources:
        provider = source['provider']
        if provider not in URLS:
            raise ValueError('Unknown provider')
        key = source['sha256']
        if key not in archives:
            archives[key] = checked_archive(source)
        raw = member(archives[key], source['manifest'])
        manifests[(provider, key)] = json.loads(raw)
    providers = {}
    for provider, plan in plans.items():
        files = {}
        for z, x, y in plan['providers'][provider]['tiles']:
            key = f'{z}/{x}/{y}.png'
            matches = [(s, manifests[(provider, s['sha256'])][key])
                       for s in sources if s['provider'] == provider
                       and key in manifests[(provider, s['sha256'])]]
            selection_key = provider + '/' + key
            if selection_key in selections:
                matches = [(s, r) for s, r in matches if s['sha256'] == selections[selection_key]]
                consumed.add(selection_key)
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous tile source: ' + provider + '/' + key)
            source, record = matches[0]
            validate_tile(provider, key, record, archives[source['sha256']])
            files[key] = dict(deepcopy(record), archive_sha256=source['sha256'])
        providers[provider] = dict(provider=provider, files=files,
            tiles_directory=f'assets/providers/{provider}/tiles',
            genuine_provider_bytes=True, original_provider_url=URLS[provider],
            runtime_external_requests_required=False, original_snapshot_equivalence=False)
    if consumed != set(selections):
        raise ValueError('Explicit tile source selection outside declared coverage')
    result = dict(version='map-provider-resources-v1', sources=deepcopy(sources),
                providers=providers, source_tasks=[dict(t, provider=provider,
                    completion_sha256=fingerprint(contracts[t['source_task_id']]))
                    for provider, plan in plans.items() for t in plan['source_tasks']],
                native_admitted=False, coverage='Declared initial view plus two tile margins; not arbitrary pan/zoom')
    if native_initial_views:
        if {v['source_task_id']for v in native_initial_views}-{c['source_task_id']for c in candidates}:
            raise ValueError('Native initial view outside resource task batch')
        result['native_initial_views']=deepcopy(native_initial_views)
        result['coverage']='Declared URL view and captured native initial route-fit view, each plus two tile margins; not arbitrary pan/zoom'
    return result


def require_candidate_resources(manifest, candidates):
    """Bind the worker's exact task/start/provider/completion before expansion.

    A worker can use a subset of the captured batch. This proves resource
    coverage only; it does not supply native controls or a success result.
    """
    if any(c.get('candidate_completion',{}).get('family')=='gps_overlay_enabled' for c in candidates):
        from .map_gps_document_resources import require_document_resources
        return require_document_resources(manifest,candidates)
    plans = provider_plans(candidates,native_initial_views=manifest.get('native_initial_views'))
    contracts = {c['source_task_id']: c['candidate_completion'] for c in candidates}
    recorded = {t['source_task_id']: t for t in manifest['source_tasks']}
    if len(recorded) != len(manifest['source_tasks']):
        raise ValueError('Duplicate resource task binding')
    for provider, plan in plans.items():
        for task in plan['source_tasks']:
            expected = dict(task, provider=provider,
                            completion_sha256=fingerprint(contracts[task['source_task_id']]))
            if recorded.get(task['source_task_id']) != expected:
                raise ValueError('Task/start/completion differs from captured resources')
            files = manifest['providers'][provider]['files']
            if any('/'.join(map(str, tile)) + '.png' not in files for tile in task['tiles']):
                raise ValueError('Captured provider does not cover declared task view')
    return True


def materialize_resources(manifest_path, expected_sha256, destination, *, candidates):
    """Create the ordinary provider files only in a fresh private directory."""
    raw = Path(manifest_path).read_bytes()
    if sha(raw) != expected_sha256:
        raise ValueError('Provider resource manifest changed')
    manifest = json.loads(raw)
    if manifest.get('version') != 'map-provider-resources-v1' or manifest.get('native_admitted') is not False:
        raise ValueError('Unrecognized resource manifest')
    if not candidates:
        raise ValueError('Explicit worker task batch required')
    require_candidate_resources(manifest, candidates)
    archives = {}
    for source in manifest['sources']:
        if source['sha256'] not in archives:
            archives[source['sha256']] = checked_archive(source)
    output = {}
    providers = deepcopy(manifest['providers'])
    for provider, spec in providers.items():
        records = {}
        for key, row in spec['files'].items():
            row = deepcopy(row)
            files = archives[row.pop('archive_sha256')]
            validate_tile(provider, key, row, files)
            records[key] = row
            for record in (row, row['original_member'], row['http_receipt']):
                name = record['member']
                if name in output and output[name] != files[name]:
                    raise ValueError('Conflicting provider member')
                output[name] = files[name]
        name = f'assets/providers/{provider}/full-tile-manifest.json'
        data = (json.dumps(records, indent=2) + '\n').encode()
        output[name] = data
        spec['files'] = records
        spec['manifest'] = dict(member=name, bytes=len(data), sha256=sha(data))
        spec['full_members'] = [dict(member=k, bytes=len(v), sha256=sha(v))
                              for k, v in output.items() if k.startswith(f'assets/providers/{provider}/')]
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in output.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return dict(assets={'frozen_tile_providers': providers}, native_admitted=False,
                resource_manifest_sha256=expected_sha256,
                runtime_external_requests_required=False)
