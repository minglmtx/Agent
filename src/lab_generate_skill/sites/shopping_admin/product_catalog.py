"""One private product-state capture in the original supervised site worker."""

from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.native_commands import NativeCommands
from .service_contract import AdminServiceSpec
from .service_commands import container
from .product_catalog_contract import ProductCatalogState
from .product_catalog_program import PRODUCT_CATALOG_PHP


class ProductCatalogReplyError(ValueError):
    def __init__(self, raw: bytes) -> None:
        self.raw_reply = raw
        super().__init__("Invalid original product catalog reply; preserve capture")


def capture_product_catalog(
    service: AdminServiceSpec,
    product_id: int,
    commands: NativeCommands,
    control: OperationControl,
) -> ProductCatalogState:
    service = AdminServiceSpec.model_validate(service)
    if type(product_id) is not int or not 0 < product_id <= 9999999999:
        raise ValueError("Product capture requires an explicit positive bounded ID")
    control.checkpoint()
    raw = commands.run(
        container(service) + ("php", "-r", PRODUCT_CATALOG_PHP, str(product_id)),
        control,
    )
    try:
        result = ProductCatalogState.model_validate_json(raw)
        if raw != result.model_dump_json().encode() or result.product_id != product_id:
            raise ValueError("Original catalog reply differs from canonical identity")
    except (ValueError, TypeError) as error:
        raise ProductCatalogReplyError(raw) from error
    control.checkpoint()
    return result
