"""Selected one-use private frontend preparation via the original file port."""

import os
import threading
from lab_generate_skill.domain.errors import InvalidTransition, OwnershipConflict
from lab_generate_skill.domain.map_services import MapServiceSpec
from lab_generate_skill.domain.map_frontend import MapFrontendPrepared
from lab_generate_skill.ports.map_services import MapFrontendFiles
from lab_generate_skill.ports.lifecycle import OperationControl
from .frontend_sources import preparation


class MapFrontendPreparation:
    def __init__(self, spec: MapServiceSpec, files: MapFrontendFiles) -> None:
        self.spec = MapServiceSpec.model_validate(spec)
        self.files = files
        self.owner = os.getpid(), threading.get_ident()
        self.state = "new"
        self.receipt: MapFrontendPrepared | None = None

    def prepare(self, control: OperationControl) -> MapFrontendPrepared:
        if self.owner != (os.getpid(), threading.get_ident()):
            raise OwnershipConflict("Original frontend preparation owner required")
        if self.state != "new":
            raise InvalidTransition("Frontend preparation cannot be repeated")
        control.checkpoint()
        self.state = "preparing"
        try:
            plan = preparation(self.spec, self.files.read(self.spec, control))
            receipt = MapFrontendPrepared.model_validate(
                self.files.apply(plan, control)
            )
            self.receipt = receipt
            receipt.check(plan)
            control.checkpoint()
            self.state = "prepared"
            return receipt
        except BaseException:
            self.state = "failed"
            raise
