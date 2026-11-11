"""Original physical caller delegated by a concrete source-claim authority.

Business claim creation stays with the construction/single source consumer.
Resource suppliers use only its original owner and actual caller verification.
"""

from typing import Protocol
from lab_generate_skill.domain.execution import RunBinding
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.scheduler import SlurmExecutionIdentity
from lab_generate_skill.domain.slurm_allocation import SlurmCgroupMembership
from lab_generate_skill.domain.lifecycle import OperationContext


class OriginalRunResourceAccess(Protocol):
    @property
    def run(self) -> RunBinding: ...
    @property
    def task(self) -> TaskBinding: ...
    @property
    def execution(self) -> SlurmExecutionIdentity: ...
    @property
    def controller(self) -> SlurmCgroupMembership: ...
    def require_caller(self, operation: OperationContext) -> None: ...
