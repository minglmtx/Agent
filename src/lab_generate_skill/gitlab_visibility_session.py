"""Opt-in source-owned native reader. Reuses Rails, never model answers."""
from contextlib import contextmanager

from .gitlab_subscription_session import ReferenceSession


class VisibilitySession(ReferenceSession):
    REFERENCE_SOURCE = 'gitlab_visibility_reference.rb'

    def project(self, site, project_id):
        if site is not self.site or type(project_id) is not int or project_id <= 0:
            raise ValueError('Exact live site and positive project ID required')
        value = self.read({'project_id': project_id},
                          self.directory / f'read-{self.sequence + 1:03d}.json')
        value.pop('seconds')
        if value.get('project_id') != project_id:
            raise ValueError('Native visibility response belongs to another project')
        return value


@contextmanager
def bind_visibility_reader(site, directory):
    """Caller owns the full control/rollout, including terminal scoring."""
    if getattr(site, '_visibility_reference_session', None) is not None:
        raise ValueError('A visibility reader is already bound')
    with VisibilitySession(site, directory) as reader:
        site._visibility_reference_session = reader
        try:
            yield reader
        finally:
            del site._visibility_reference_session
