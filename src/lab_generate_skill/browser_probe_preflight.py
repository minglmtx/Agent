"""Verify executable data before a native browser probe starts a website."""
import hashlib
import json
import os
from pathlib import Path
from .native_runtime_assets import required


def verify(project, contracts, *, manifest_path=None):
    root = Path(project).resolve()
    manifest_path = manifest_path or os.environ.get('LAB_FROZEN_NATIVE_ASSET_MANIFEST')
    if not manifest_path:
        raise ValueError('Frozen probe asset manifest required')
    declared = json.loads(Path(manifest_path).read_text())
    names = {'configs/browser-page-wait.json'}
    for contract in contracts:
        names.update(required(contract))
        if contract.get('gitlab_persisted_goal', {}).get('kind') == 'visibility':
            names.update(('src/lab_generate_skill/gitlab_visibility_reference.rb',
                          'src/lab_generate_skill/gitlab_subscription_session.rb',
                          'src/lab_generate_skill/gitlab_native_csv_consumer.rb'))
    hashes = {}
    for name in sorted(names):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Required frozen probe asset unavailable: ' + name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if declared.get(name) != digest:
            raise ValueError('Unpinned or modified frozen probe asset: ' + name)
        hashes[name] = digest
    cfg = json.loads((root / 'configs/browser-page-wait.json').read_text())
    for domain in {c['domain'] for c in contracts}:
        site = cfg.get('sites', {}).get(domain, {})
        budget = site.get('max_wait_ms')
        if type(budget) is not int or not 0 < budget <= 60000:
            raise ValueError('Invalid packaged browser wait budget: ' + domain)
    return dict(assets=hashes, websites_started=0, actor_attempts=0, api_calls=0)
