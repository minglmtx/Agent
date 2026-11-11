"""Separate cold website pool for the provenance-sensitive local report owner.

Reuse the existing profile worker/backend cleanup plumbing. The report baseline
replaces the site's full snapshot; it must never be borrowed by another family.
The original native lifecycle, gates and final-state evaluator stay unchanged.
"""
from .reddit_media_local_profile import MediaLocalProfile

VERSION = 'reddit-local-report-owner-profile-v1'

class ReportProfile(MediaLocalProfile):
    def __init__(self, registry):
        self.registry = registry
        self.modules = {n: m for n, m in registry.loaded.items() if n.startswith('reddit_report_')}
        self.workers, self.holders = [], []
        self.closed = self.running = False
        pins = registry.config['runtime_files']
        self.binding = (VERSION, tuple(sorted((n, h) for n, h in pins.items()
            if n.startswith('scripts/native_reddit/report/') or n.endswith('/reddit_report_profile.py'))))
        self.require_current()

    def require_current(self):
        if self.closed:
            raise ValueError('Report profile is closed')
        self.registry.require_current()

    def module(self, name):
        self.require_current()
        if name not in self.modules:
            raise ValueError('Unknown report owner module')
        return self.modules[name]

    def prepare(self, site):
        self.require_current()
        if site.domain != 'reddit':
            raise ValueError('Local reports require Reddit')
        if any(getattr(site, name, None) is not None for name in
               ('native_media_owner', 'local_ui_extension')):
            raise ValueError('Report profile cannot borrow media/local UI baselines')
        lifecycle = self.module('reddit_report_lifecycle')
        owner = getattr(site, 'report_ui_owner', None)
        if owner is not None and (type(owner) is not lifecycle.ReportLifecycle
                or owner.site is not site or not owner.installed or not owner.verify_config()):
            raise ValueError('Report owner or full-reset configuration differs')
        # OrdinaryHooks.prepare resolves the native account and runs the exact
        # full private-baseline comparison after ensure_report. Never seed here.

    def finish(self, site):
        lifecycle = self.module('reddit_report_lifecycle')
        owner = getattr(site, 'report_ui_owner', None)
        if owner is None:
            # Original installation assigns the owner before starting a listener.
            return {'report_not_initialized': True}
        if type(owner) is not lifecycle.ReportLifecycle or owner.site is not site:
            raise ValueError('Cannot close another report owner')
        receipt = owner.close()
        if not lifecycle.cleanup_verified(receipt):
            raise RuntimeError('Report requests must join before reset/site shutdown')
        return receipt
