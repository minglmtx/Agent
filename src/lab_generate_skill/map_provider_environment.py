"""Worker-owned frozen map providers, installed before the reset baseline.

This is an environment profile, not task admission. Provider images are shared
as immutable archives; each website owns its ports, source edits and service.
"""
import hashlib
import json
from pathlib import Path

from .io_utils import atomic_write_json
from .map_provider_contract import validate_resource_family
from .map_provider_resources import materialize_resources, require_candidate_resources
from .map_frozen_provider_runtime import FrozenProviderServer, NativeProviderExtension

VERSION = 'map-frozen-provider-environment-v1'


def read_profile(path):
    path = Path(path)
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get('version') != VERSION or value.get('original_snapshot_equivalence') is not False
            or value.get('runtime_external_requests') is not False):
        raise ValueError('Explicit frozen provider environment revision required')
    loaded = {}
    for name in ('resources','contracts'):
        ref = value[name]
        file = Path(ref['path'])
        if not file.is_absolute() or file.is_symlink() or not file.is_file():
            raise ValueError('Pinned regular provider manifest required')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != ref['sha256']:
            raise ValueError('Provider manifest content changed: '+name)
        loaded[name] = json.loads(data)
    candidates = loaded['contracts']['tasks']
    if (not candidates or any(c.get('domain') != 'map' or c.get('split') != 'train'
            or c.get('heldout_quarantine') is not False
            for c in candidates)):
        raise ValueError('Declared same-family training provider candidates required')
    for candidate in candidates:
        validate_resource_family(candidate.get('candidate_completion',{}))
        if candidate['candidate_completion']['family']=='provider_before_export':
            from .map_ordered_export import validate
            validate(candidate)
    require_candidate_resources(loaded['resources'], candidates)
    binding = dict(version=VERSION,manifest_sha256=hashlib.sha256(raw).hexdigest(),
        resources_sha256=value['resources']['sha256'],contracts_sha256=value['contracts']['sha256'])
    return value, candidates, binding


class ProviderEnvironment:
    def __init__(self, site, manifest):
        self.site = site
        self.value, self.candidates, self.binding = read_profile(manifest)
        self.server = self.extension = None
        self.installed = False

    def install(self):
        site = self.site
        if site.reset_guard is not None or self.installed:
            raise ValueError('Provider profile must precede the one reset baseline')
        if not (site.with_tiles and site.with_geographic_baseline and site.track_changes):
            raise ValueError('Complete native tracked Map environment required')
        root = site.state/'frozen-provider-assets'
        try:
            profile = materialize_resources(self.value['resources']['path'],self.value['resources']['sha256'],
                root,candidates=self.candidates)
            self.server = FrozenProviderServer(profile,root)
            if any(c['candidate_completion']['family'] == 'gps_overlay_enabled' for c in self.candidates):
                self.extension = NativeProviderExtension(site,self.server,gps_document=True)
            else:
                self.extension = NativeProviderExtension(site,self.server)
            changes = self.extension.install()
            self.installed = True
            atomic_write_json(site.logs/'frozen-provider-environment.json',dict(
                binding=self.binding,extension=changes,baseline_required_after_install=True,
                actor_actions=0,task_admissions=0))
            return self.binding
        except BaseException:
            self.close()
            raise

    def require_owned(self):
        if not self.installed or self.server is None or self.server.closed or not self.server.thread.is_alive():
            raise ValueError('Worker-owned provider service is unavailable')
        if self.extension.netloc not in self.site.allowed_netlocs:
            raise ValueError('Provider service is not part of this private website')

    def close(self):
        # Always stop the owned HTTP service, even if source restoration fails.
        receipt = {}
        try:
            if self.extension is not None:
                receipt['source_restoration'] = self.extension.close()
        finally:
            if self.server is not None:
                self.server.close()
                receipt['transport'] = self.server.snapshot()
            self.installed = False
            atomic_write_json(self.site.logs/'frozen-provider-cleanup.json',receipt)
        return receipt
