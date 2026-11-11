"""Capture original full query protection via this same live Shopping worker."""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_commands import container
from .service_contract import ShoppingServiceSpec
from .native_static import NativeStaticPublication
from .query_state import QueryProtectedState, QueryProtection, LocalMail
from .query_programs import CORE_FINGERPRINT, LOCAL_MAIL
from .tasks.order_eta_programs import PROTECTION


def capture_query_protection(
    spec: ShoppingServiceSpec,
    native_assets: bytes,
    commands: NativeCommands,
    control: OperationControl,
) -> QueryProtectedState:
    spec = ShoppingServiceSpec.model_validate(spec)
    assets = NativeStaticPublication.model_validate_json(native_assets)
    control.checkpoint()
    base = container(spec)
    protection = QueryProtection.model_validate_json(
        commands.run(base + ("php", "-r", PROTECTION), control)
    )
    fingerprint = commands.run(base + ("php", "-r", CORE_FINGERPRINT), control).decode(
        "ascii"
    )
    mail = LocalMail.model_validate_json(
        commands.run(base + ("php", "-r", LOCAL_MAIL), control)
    )
    return QueryProtectedState(
        protection=protection,
        core_fingerprint=fingerprint,
        native_static_assets=assets,
        local_mail=mail,
    )
