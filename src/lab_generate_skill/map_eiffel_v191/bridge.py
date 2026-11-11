from lab_generate_skill.map_scope_v190.adapter import Bridge
from .adapter import Adapter as QualifiedSearch
from .evaluate import SOURCE


class EiffelAdapter(Bridge):
    AUTHORIZED_TARGET_WRITES=False
    FEEDBACK_VERSIONS=QualifiedSearch.FEEDBACK_VERSIONS

    def enabled(self,c):
        return (c.get("source_task_id")==SOURCE and c.get("domain")=="map"
                and c.get("validation_scope")==self.FEEDBACK_VERSIONS[0])

    feedback=QualifiedSearch.feedback
