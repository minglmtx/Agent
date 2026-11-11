"""Original registered site view; construction of a view grants no resource."""

from typing import Protocol
from lab_generate_skill.domain.site_resource import SiteResourceStarted
from .site_tasks import SiteTasks
from .site_capture import ParentSiteCapture
from .site_resume import ParentSiteResume


class SiteHandle(Protocol):
    @property
    def site(self) -> SiteResourceStarted: ...

    @property
    def tasks(self) -> SiteTasks: ...

    @property
    def capture(self) -> ParentSiteCapture: ...

    @property
    def resume(self) -> ParentSiteResume: ...
