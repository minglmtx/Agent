"""Map one explicitly owned five-port reservation to Admin service roles.

No allocation, environment variables or legacy singleton. The caller must keep
this lease through startup/cleanup; these numbers are not closure/authority.
"""

from lab_generate_skill.ports.local_ports import LocalPortLease
from .service_contract import AdminPorts


def admin_ports(lease: LocalPortLease) -> AdminPorts:
    values = lease.ports
    if type(values) is not tuple or len(values) != 5:
        raise ValueError("Admin requires one exact five-port lease")
    return AdminPorts(
        web=values[0],
        database=values[1],
        redis=values[2],
        search=values[3],
        transport=values[4],
    )
