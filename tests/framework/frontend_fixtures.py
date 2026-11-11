"""Synthetic frontend facts for unit protocols only, never real writer authority."""

from lab_generate_skill.domain.process_identity import ProcessIdentity
from lab_generate_skill.domain.native_namespace import (
    NativeNamespaceIdentity,
    NativeNamespaceStopped,
)
from lab_generate_skill.sites.shopping_admin.frontend_contract import (
    AdminFrontendStopped,
    AdminBackendDrain,
)
from lab_generate_skill.sites.shopping_admin.service_contract import AdminServiceSpec


def namespace(name: str) -> NativeNamespaceIdentity:
    index = {"nginx": 0, "php": 1}[name]
    return NativeNamespaceIdentity(
        service=name,
        launcher=ProcessIdentity(
            node_id="node", boot_id="boot", process_id=100 + index * 10, start_ticks=100
        ),
        init=ProcessIdentity(
            node_id="node", boot_id="boot", process_id=101 + index * 10, start_ticks=101
        ),
        namespace_device=4,
        namespace_inode=500 + index,
    )


def stopped(name: str) -> NativeNamespaceStopped:
    return NativeNamespaceStopped(
        original=namespace(name), init_exit_observed=True, launcher_returncode=-9
    )


def frontend(spec: AdminServiceSpec) -> AdminFrontendStopped:
    return AdminFrontendStopped(
        service=spec,
        namespaces=(stopped("nginx"), stopped("php")),
        backend=AdminBackendDrain(
            other_sql_connections=0,
            sql_transactions=0,
            redis_clients=1,
            redis_blocked=0,
            search_write_tasks=0,
        ),
    )
