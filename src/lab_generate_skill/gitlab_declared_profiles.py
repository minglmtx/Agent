"""One explicit GitLab baseline per isolated worker or alternating slot."""
from copy import deepcopy
from pathlib import Path

from . import gitlab_hierarchy_fixture as hierarchy
from . import gitlab_metrics_fixture as metrics


def profile_for_contracts(cases, domain):
    if not cases:
        raise ValueError('Nonempty initial-state profile required')
    profiles = []
    for case in cases:
        h = hierarchy.declaration_for(case)
        m = metrics.declaration_for(case)
        if h is not None and m is not None:
            raise ValueError('Only one declared GitLab baseline per worker')
        value = ({'kind': 'hierarchy', 'declaration': h} if h is not None else
                 {'kind': 'metrics', 'declaration': m} if m is not None else None)
        if value is not None and domain != 'gitlab':
            raise ValueError('GitLab initial state belongs to GitLab only')
        profiles.append(value)
    if any(value != profiles[0] for value in profiles):
        raise ValueError('Different declared initial states require isolated workers')
    return deepcopy(profiles[0])


def validate_profile(profile):
    if profile is None:
        return None
    if not isinstance(profile, dict) or set(profile) != {'kind', 'declaration'}:
        raise ValueError('Explicit GitLab initial-state profile required')
    module = {'hierarchy': hierarchy, 'metrics': metrics}.get(profile['kind'])
    if module is None:
        raise ValueError('Unknown GitLab initial-state profile')
    return dict(kind=profile['kind'], declaration=module.validate_declaration(profile['declaration']))


def apply_profile(site, profile, username, directory):
    profile = validate_profile(profile)
    if profile is None:
        if any(getattr(site, k, None) is not None for k in ('prepared_hierarchy', 'prepared_metrics')):
            raise ValueError('Declared fixture cannot be reused for a seed-only task')
        return None
    module = hierarchy if profile['kind'] == 'hierarchy' else metrics
    attribute = 'prepared_' + profile['kind']
    other = 'prepared_metrics' if profile['kind'] == 'hierarchy' else 'prepared_hierarchy'
    if getattr(site, other, None) is not None:
        raise ValueError('Another initial-state fixture already owns this site')
    receipt = getattr(site, attribute, None)
    if receipt is not None:
        if receipt.get('declaration') != profile['declaration'] or receipt.get('username') != username:
            raise ValueError('Prepared baseline belongs to another target or account')
        if module is hierarchy:
            hierarchy.require_initializer_version(receipt)
        else:
            metrics.require_receipt(receipt, profile['declaration'], username)
        return receipt
    return module.prepare(site, username, profile['declaration'], directory)


def prepare_batch(site, cases, username, directory):
    return apply_profile(site, profile_for_contracts(cases, 'gitlab'), username, directory)


def new_site(root, logs, profile, **options):
    """Initialize each real slot before reset prefetch or model use.

    Return an actual site object, not a discarded generator context manager;
    ordinary pool cleanup continues to own its lifetime.
    """
    from .gitlab_site import IsolatedGitlabSite
    from .site_auth import credentials
    profile = validate_profile(profile)

    class DeclaredSite(IsolatedGitlabSite):
        def __enter__(self):
            super().__enter__()
            self.domain = 'gitlab'
            try:
                apply_profile(self, profile, credentials(root, 'gitlab')['username'],
                              Path(logs)/'declared-initial-state')
            except BaseException:
                self.__exit__(None, None, None)
                raise
            return self

    return DeclaredSite(root, logs, **options)
