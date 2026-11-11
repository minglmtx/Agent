"""Original six-service generation identity; no replacement of held resources."""

from lab_generate_skill.domain.native_namespace import NativeNamespaceIdentity
from lab_generate_skill.domain.native_quiescence import NativeServiceQuiescence
from .service_commands import SERVICE_NAMES


def new_generation(
    old: NativeServiceQuiescence, pins: tuple[NativeNamespaceIdentity, ...]
) -> None:
    prior = {p.original.service: p.original for p in old.namespaces}
    if tuple(p.service for p in pins) != SERVICE_NAMES or set(prior) != set(
        SERVICE_NAMES
    ):
        raise ValueError("All six original GitLab service namespaces required")
    for pin in pins:
        previous = prior[pin.service]
        for before, after in (
            (previous.launcher, pin.launcher),
            (previous.init, pin.init),
        ):
            if (
                before == after
                or (before.node_id, before.boot_id) != (after.node_id, after.boot_id)
                or after.start_ticks < before.start_ticks
            ):
                raise ValueError(
                    "GitLab generation reused a closed process or changed original host/boot/order"
                )
