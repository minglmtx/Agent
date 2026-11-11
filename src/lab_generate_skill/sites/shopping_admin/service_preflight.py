"""Validate fixed native service programs before expensive seed extraction."""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import AdminServiceSpec
from .service_commands import container
from .service_programs import SEED, CONFIGURE, HEALTH, MAIL_SINK


def preflight_services(
    spec: AdminServiceSpec, commands: NativeCommands, control: OperationControl
) -> None:
    base = container(spec, seeded=False)
    commands.run(base + ("sh", "-n", "-c", SEED), control)
    for program in (CONFIGURE, HEALTH, MAIL_SINK.removeprefix("<?php")):
        commands.run(base + ("php", "-r", "if(false){" + program + "}"), control)
